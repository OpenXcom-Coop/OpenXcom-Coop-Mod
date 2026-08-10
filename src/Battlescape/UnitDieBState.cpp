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

#include "UnitDieBState.h"
#include "TileEngine.h"
#include "BattlescapeState.h"
#include "Map.h"
#include "../Engine/Game.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"
#include "../Mod/Mod.h"
#include "../Engine/Sound.h"
#include "../Engine/RNG.h"
#include "../Engine/Options.h"
#include "../Engine/Language.h"
#include "../Mod/Armor.h"
#include "InfoboxOKState.h"
#include "InfoboxState.h"
#include "../Savegame/Node.h"
#include "../CoopMod/SharedEcon.h" // coop (PRD-P4): Tier-A corpse id-manifest

namespace OpenXcom
{

/**
 * Sets up an UnitDieBState.
 * @param parent Pointer to the Battlescape.
 * @param unit Dying unit.
 * @param damageType Type of damage that caused the death.
 * @param noSound Whether to disable the death sound.
 */
UnitDieBState::UnitDieBState(BattlescapeGame* parent, BattleUnit* unit, const RuleDamageType* damageType, bool noSound, bool coop_death) : BattleState(parent),
	_unit(unit), _damageType(damageType), _noSound(noSound), _coop_death(coop_death), _extraFrame(0), _overKill(unit->getOverKillDamage())
{

	// coop 
	if (_parent->isCoop() == true && _parent->getCoopMod()->getHost() == false && _coop_death == false)
	{
		return;
	}

	// don't show the "fall to death" animation when a unit is blasted with explosives or he is already unconscious
	if (!_damageType->isDirect() || _unit->getStatus() == STATUS_UNCONSCIOUS)
	{

		/********************************************************
		Proclamation from Lord Xenu:

		any unit that is going to skip its death pirouette
		MUST have its direction set to 3 first.

		Failure to comply is treason, and treason is punishable
		by death. (after being correctly oriented)

		********************************************************/
		_unit->setDirection(3);


		_unit->instaFalling();
		if (_parent->getSave()->isBeforeGame())
		{
			convertUnitToCorpse();
			_extraFrame = 3; // shortcut to popState()
		}
	}
	else
	{
		if (_unit->getFaction() == FACTION_PLAYER)
		{
			_parent->getMap()->setUnitDying(true);
		}
		_parent->setStateInterval(BattlescapeState::DEFAULT_ANIM_SPEED);
		if (_unit->getDirection() != 3)
		{
			_parent->setStateInterval(BattlescapeState::DEFAULT_ANIM_SPEED / 3);
		}
	}

	_unit->clearVisibleTiles();
	_unit->clearVisibleUnits();
	_unit->freePatrolTarget();

	if (!_parent->getSave()->isBeforeGame() && _unit->getFaction() == FACTION_HOSTILE)
	{
		std::vector<Node *> *nodes = _parent->getSave()->getNodes();
		if (!nodes) return; // this better not happen.

		for (auto* node : *nodes)
		{
			if (!node->isDummy() && Position::distanceSq(node->getPosition(), _unit->getPosition()) < 4)
			{
				node->setType(node->getType() | Node::TYPE_DANGEROUS);
			}
		}
	}
}

/**
 * Deletes the UnitDieBState.
 */
UnitDieBState::~UnitDieBState()
{
}

/**
 * coop: stamps the host's kill ATTRIBUTION on a death packet.
 *
 * `killedBy` and `murdererId` are written by BattlescapeGame::checkForCasualties -
 * on the machine that RESOLVED the death, before it pushes this state - and they
 * were the one part of a death that never crossed the wire. The peer got away with
 * that whenever it happened to run its own checkForCasualties over the same victim
 * (it is displaying the attack, so the murderer is resolvable there too), which is
 * every death caused by an action the peer replays. It does NOT happen for a death
 * the peer never replays as a local attack chain - a reaction-fire kill during the
 * ALIEN side is the everyday one - and there the alien keeps the BattleUnit ctor
 * default `_killedBy = its own faction`.
 *
 * That is a scored, persisted divergence, not a cosmetic one: DebriefingState
 * counts STR_ALIENS_KILLED as `oldFaction == FACTION_HOSTILE && killedBy() ==
 * FACTION_PLAYER` over each machine's OWN save (prepareDebriefing runs on both,
 * ahead of the host's debriefing packet), so the two players saw different kill
 * counts and different scores for the same battle - and `killedBy` is saved.
 *
 * Written on BOTH death packets: `unit_death` so the peer has it while the death
 * is still being displayed, `after_unit_death` as the definitive re-stamp once the
 * death has fully resolved. Applying it twice is idempotent.
 */
void UnitDieBState::coopWriteKillAttribution(Json::Value& root) const
{
	root["killedBy"] = (int)_unit->killedBy();
	root["murdererId"] = _unit->getMurdererId();
}

/**
 * coop (PRD-I3 SEAM-4): every LIVING unit's absolute morale after this casualty.
 *
 * BattlescapeGame::checkForCasualties applies a morale change to EVERY living unit
 * on any death/stun (the losing squad loses morale, the winning squad gains, and a
 * murderer gets a kill bonus) BEFORE it pushes this state - so by the time this
 * packet is sent getMorale() is the host's FINAL post-casualty value for all of
 * them. A PARALLEL thin client never runs checkForCasualties for a kill it only
 * DISPLAYS (BattlescapeGame::coopDeath just animates the death; a reaction-fire /
 * alien-side kill is never a local attack chain there), so without this the whole
 * squad's morale stays at its pre-casualty value until next_turn's bulk re-ship one
 * side later - a per-action unitsStats(morale) divergence across every living
 * bystander. `hit_unit` already ships the VICTIM's own post-damage morale; this is
 * the OTHER units the casualty moved.
 *
 * Shipped as an ABSOLUTE {id -> morale} snapshot, so applying it is idempotent: it
 * cannot double-apply against a chain the client also replays, and it is safe against
 * next_turn's later bulk re-ship. The receiver applies it ONLY on the parallel
 * non-host machine (parallelTurnActive() && !getHost()); a classic client replays the
 * attack and runs its OWN checkForCasualties, so it never reads this and stays
 * byte-identical. Additive - an older peer ignores the field. Written on BOTH death
 * packets, mirroring coopWriteKillAttribution: `unit_death` while the death displays,
 * `after_unit_death` as the freshest re-stamp (a chain-reaction casualty between
 * init() and deinit() moves morale again).
 */
void UnitDieBState::coopWriteBystanderMorale(Json::Value& root) const
{
	Json::Value arr(Json::arrayValue);
	for (auto* bu : *_parent->getSave()->getUnits())
	{
		if (bu->isOut())
			continue;
		Json::Value entry;
		entry["id"] = bu->getId();
		entry["morale"] = bu->getMorale();
		arr.append(entry);
	}
	root["bystander_morale"] = arr;
}

/**
 * coop (PRD-P10): `after_unit_death` moved here from the DESTRUCTOR.
 *
 * A BattleState is destroyed by cleanupDeleted(), which runs at a turn boundary
 * and at a couple of UI transitions - NOT when the state finishes. So this
 * packet, which carries the death's final unit state AND the PRD-P4 corpse
 * id-manifest, was being sent up to a whole side after the corpse existed
 * (measured: 82 s on a soak run). For every second of that window the peer's
 * corpse carried an id off the host's, and any census taken in it disagreed -
 * including the one after the alien side, because a death DURING that side does
 * not reach a cleanupDeleted() until the boundary AFTER the census.
 *
 * deinit() is called by popState() the instant the state pops, exactly once per
 * pop, which is what "the death is over" actually means.
 */
void UnitDieBState::deinit()
{

	// coop
	if ((_parent->isCoop() == true && _coop_death == false && _parent->getCoopMod()->getHost() == true))
	{

		// coop
		Json::Value root;

		root["state"] = "after_unit_death";

		root["status"] = _parent->getCoopMod()->unitstatusToInt(_unit->getStatus());

		root["unit_id"] = _unit->getId();

		root["time"] = _unit->getTimeUnits();
		root["health"] = _unit->getHealth();
		root["energy"] = _unit->getEnergy();
		root["morale"] = _unit->getMorale();
		root["mana"] = _unit->getMana();
		root["stunlevel"] = _unit->getStunlevel();

		root["setDirection"] = _unit->getDirection();
		root["setFaceDirection"] = _unit->getFaceDirection();

		// motions point
		root["motionpoints"] = _unit->getMotionPoints();

		// new
		root["respawn"] = _unit->getRespawn();

		bool isTile = false;

		if (_unit->getTile())
		{

			isTile = true;
		}

		root["isTile"] = isTile;

		// coop: the kill ATTRIBUTION, the host's final word on it.
		coopWriteKillAttribution(root);

		// coop (PRD-I3 SEAM-4): every living unit's absolute post-casualty morale.
		coopWriteBystanderMorale(root);

		// coop (PRD-P4): the ids this death's corpses were minted with. This is the
		// FIRST packet after convertUnitToCorpse() has run, so it is where the
		// manifest belongs; writes nothing when the death produced no corpse (an
		// overkill, a carried body - convertToCorpse() reuses the body item's id -
		// or a respawn, which ships its own manifest on `convertUnit`).
		SharedEcon::flushSpawnRecord(root, "corpse", _unit->getId());

		_parent->sendPacketData(root.toStyledString());
	}

}

void UnitDieBState::init()
{

	// coop 
	if (_parent->isCoop() == true && _parent->getCoopMod()->getHost() == false && _coop_death == false)
	{
		return;
	}

	// coop
	if ((_parent->isCoop() == true && _coop_death == false && _parent->getCoopMod()->getHost() == true))
	{

		// coop
		Json::Value root;

		root["state"] = "unit_death";

		root["status"] = _parent->getCoopMod()->unitstatusToInt(_unit->getStatus());

		root["unit_id"] = _unit->getId();
		root["pos_x"] = _unit->getPosition().x;
		root["pos_y"] = _unit->getPosition().y;
		root["pos_z"] = _unit->getPosition().z;

		root["time"] = _unit->getTimeUnits();
		root["health"] = _unit->getHealth();
		root["energy"] = _unit->getEnergy();
		root["morale"] = _unit->getMorale();
		root["mana"] = _unit->getMana();
		root["stunlevel"] = _unit->getStunlevel();

		root["setDirection"] = _unit->getDirection();
		root["setFaceDirection"] = _unit->getFaceDirection();

		// motions points (fix)
		root["motionpoints"] = _unit->getMotionPoints();

		root["damageType"] = _parent->getCoopMod()->ItemDamageTypeToInt(_damageType->ResistType);
		root["noSound"] = _noSound;

		// coop (PRD-P9 soak finding): whether the dying unit still stands on a
		// tile. Only `after_unit_death` used to carry this, and the peer read the
		// MISSING key here as false - so it unlinked the tile before its own
		// UnitDieBState ran, and convertUnitToCorpse's `dropItems && getTile()`
		// test then skipped itemDropInventory. The dead soldier's whole kit
		// stayed in its inventory on the peer while it lay on the ground on the
		// executor - a strict-census divergence on every equipped casualty.
		root["isTile"] = (_unit->getTile() != nullptr);

		// new
		root["respawn"] = _unit->getRespawn();

		bool isTile = false;

		if (_unit->getTile())
		{

			isTile = true;
		}

		root["isTile"] = isTile;

		// coop: the kill ATTRIBUTION - see coopWriteKillAttribution(). Both
		// killedBy and murdererId are already final here: checkForCasualties
		// stamps them and only then pushes this state.
		coopWriteKillAttribution(root);

		// coop (PRD-I3 SEAM-4): every living unit's absolute post-casualty morale -
		// see coopWriteBystanderMorale(). checkForCasualties applied the bystander
		// morale change before pushing this state, so getMorale() is final here.
		coopWriteBystanderMorale(root);

		_parent->sendPacketData(root.toStyledString());

	}

	// check for presence of battlestate to ensure that we're not pre-battle
	// check for the unit's tile to make sure we're not trying to kill a dead guy
	if (_parent->getSave()->getBattleState() && !_unit->getTile())
	{
		if (_unit->getOriginalFaction() == FACTION_PLAYER)
		{
			if (_unit->getNotificationShown() == 2)
			{
				// skip completely
				_parent->popState();
			}
			else if (_unit->getNotificationShown() == 1)
			{
				// can't skip this (there could still be a death notification), but at least speed it up
				_parent->setStateInterval(1);
			}
		}
		else
		{
			_parent->popState();
		}
	}

}

/**
 * Runs state functionality every cycle.
 * Progresses the death, displays any messages, checks if the mission is over, ...
 */
void UnitDieBState::think()
{

	// coop
	if (_parent->isCoop() == true && _parent->getCoopMod()->getHost() == false && _coop_death == false)
	{
		// coop (PRD-P9 soak finding): cancel the LOCAL death - the peer never
		// decides who dies - but never RESURRECT. The executor's `unit_death` may
		// already have arrived and set this unit STATUS_DEAD (it is sent from
		// UnitDieBState::init, ahead of the damage packets the peer's own
		// checkForCasualties reacts to), and writing STATUS_STANDING over it left
		// the peer holding a soldier that was dead on the executor and standing
		// here, on 0 HP, for the rest of the battle.
		if (!_unit->isOut())
		{
			_unit->setCoopStatus(STATUS_STANDING);
		}
		_parent->popState();
		return;
	}

	if (_extraFrame == 3)
	{
		_parent->popState();
		return;
	}
	if (_unit->getDirection() != 3 && _damageType->isDirect())
	{
		int dir = _unit->getDirection() + 1;
		if (dir == 8)
		{
			dir = 0;
		}
		_unit->lookAt(dir);
		_unit->turn();
		if (dir == 3)
		{
			_parent->setStateInterval(BattlescapeState::DEFAULT_ANIM_SPEED);
		}
	}
	else if (_unit->getStatus() == STATUS_COLLAPSING)
	{
		_unit->keepFalling();
	}
	else if (!_unit->isOut())
	{
		_unit->startFalling();

		if (!_noSound)
		{
			playDeathSound();
		}
		if (_unit->getRespawn())
		{
			while (_unit->getStatus() == STATUS_COLLAPSING)
			{
				_unit->keepFalling();
			}
		}
	}
	if (_extraFrame == 2)
	{
		_parent->getMap()->setUnitDying(false);
		_parent->getTileEngine()->calculateLighting(LL_ITEMS, _unit->getPosition(), _unit->getArmor()->getSize());
		_parent->getTileEngine()->calculateFOV(_unit->getPosition(), _unit->getArmor()->getSize(), false); //Update FOV for anyone that can see me
		_parent->popState();
		// coop
		if (_unit->getOriginalFaction() == FACTION_PLAYER && ((_parent->getCoopMod()->getCoopStatic() == true && _parent->getCoopMod()->getHost() == true) || _parent->getCoopMod()->getCoopStatic() == false))
		{
			Game *game = _parent->getSave()->getBattleState()->getGame();
			if (_unit->getStatus() == STATUS_DEAD)
			{
				if (_damageType->ResistType == DT_NONE && !_unit->getSpawnUnit())
				{
					// Note: yes, this condition is necessary, init() will filter out most duplicates, but not everything
					if (_unit->getNotificationShown() < 2)
					{
						_unit->setNotificationShown(2);
						game->pushState(new InfoboxOKState(game->getLanguage()->getString("STR_HAS_DIED_FROM_A_FATAL_WOUND", _unit->getGender()).arg(_unit->getName(game->getLanguage()))));
					}
				}
				else if (Options::battleNotifyDeath && _unit->getGeoscapeSoldier() != 0)
				{
					// Note: yes, this condition is necessary, init() will filter out most duplicates, but not everything
					if (_unit->getNotificationShown() < 2)
					{
						_unit->setNotificationShown(2);
						game->pushState(new InfoboxState(game->getLanguage()->getString("STR_HAS_BEEN_KILLED", _unit->getGender()).arg(_unit->getName(game->getLanguage()))));
					}
				}
			}
			else if (_unit->indicatorsAreEnabled())
			{
				if (_unit->getNotificationShown() < 1)
				{
					_unit->setNotificationShown(1);
					game->pushState(new InfoboxOKState(game->getLanguage()->getString("STR_HAS_BECOME_UNCONSCIOUS", _unit->getGender()).arg(_unit->getName(game->getLanguage()))));
				}
			}
		}

		// coop
		if (_parent->isCoop() == true && _parent->getCoopMod()->getHost() == true)
		{
			// if all units from either faction are killed - auto-end the mission.
			if (_parent->getSave()->getSide() == FACTION_PLAYER)
			{
				_parent->autoEndBattle();
			}
		}

	}
	else if (_extraFrame == 1)
	{
		_extraFrame++;
	}
	else if (_unit->isOut())
	{
		_extraFrame = 1;
		if (!_noSound && !_damageType->isDirect() && _unit->getStatus() != STATUS_UNCONSCIOUS)
		{
			playDeathSound();
		}
		if (_unit->getStatus() == STATUS_UNCONSCIOUS && !_unit->getCapturable())
		{
			_unit->instaKill();
		}
		_unit->resetTurnsSince();
		if (_unit->getSpawnUnit() && !_overKill)
		{
			if (!_unit->getAlreadyRespawned())
			{
				// converts the dead zombie to a chryssalid
				_parent->convertUnit(_unit);
			}
		}
		else
		{
			convertUnitToCorpse();
		}

		_parent->getSave()->clearUnitSelection(_unit);
	}

}

/**
 * Unit falling cannot be cancelled.
 */
void UnitDieBState::cancel()
{
}

/**
 * Converts unit to a corpse (item).
 */
void UnitDieBState::convertUnitToCorpse()
{
	Position lastPosition = _unit->getPosition();
	int size = _unit->getArmor()->getSize();
	bool dropItems = (_unit->hasInventory() &&
		(!Options::weaponSelfDestruction ||
		(_unit->getOriginalFaction() != FACTION_HOSTILE || _unit->getStatus() == STATUS_UNCONSCIOUS)));

	// coop (PRD-P10): the replay has reached its corpse creation, so the parked
	// manifest is now unambiguously about the corpse the loop below mints. Cleared
	// BEFORE removeUnconsciousBodyItem so the two can never be confused again.
	SharedEcon::clearCorpseReplayPending(_unit->getId());

	if (!_noSound)
	{
		_parent->getSave()->getBattleState()->resetUiButton();
	}
	// remove the unconscious body item corresponding to this unit, and if it was being carried, keep track of what slot it was in
	if (lastPosition != TileEngine::invalid)
	{
		_parent->getSave()->removeUnconsciousBodyItem(_unit);
	}

	// move inventory from unit to the ground
	if (dropItems && _unit->getTile())
	{
		_parent->getTileEngine()->itemDropInventory(_unit->getTile(), _unit);
	}

	// remove unit-tile link
	_unit->setTile(nullptr, _parent->getSave());

	if (lastPosition == TileEngine::invalid) // we're being carried
	{
		if (_overKill)
		{
			_parent->getSave()->removeUnconsciousBodyItem(_unit);
		}
		else
		{
			// replace the unconscious body item with a corpse in the carrying unit's inventory
			for (auto* bi : *_parent->getSave()->getItems())
			{
				if (bi->getUnit() == _unit)
				{
					auto* corpseRules = _unit->getArmor()->getCorpseBattlescape()[0]; // we're in an inventory, so we must be a 1x1 unit
					bi->convertToCorpse(corpseRules);
					break;
				}
			}
		}
	}
	else
	{
		if (!_overKill)
		{
			// coop (PRD-P4): a Tier-A spawn. The corpse SET is deterministic (the
			// armor's corpse list, size^2 of them) so both machines create the same
			// items - but each mints its own ids off its own counter, and once those
			// disagree every later id-keyed packet lands on the wrong instance. Only
			// one of these two is ever live: the record on the host (its ids ride
			// `after_unit_death`), the guard on the peer.
			SharedEcon::CoopSpawnRecord coopRec("corpse", _unit->getId());
			SharedEcon::CoopSubjectGuard coopGuard(_parent->getSave(), "corpse", _unit->getId());
			int i = size * size - 1;
			for (int y = size - 1; y >= 0; --y)
			{
				for (int x = size - 1; x >= 0; --x)
				{
					BattleItem *corpse = _parent->getSave()->createItemForTile(_unit->getArmor()->getCorpseBattlescape()[i], nullptr, _unit);
					_parent->dropItem(lastPosition + Position(x,y,0), corpse, false);
					--i;
				}
			}
		}
		else
		{
			_parent->getSave()->getTileEngine()->applyGravity(_parent->getSave()->getTile(lastPosition));
		}
	}
}

/**
 * Plays the death sound.
 */
void UnitDieBState::playDeathSound()
{
	const std::vector<int> &sounds = _unit->getDeathSounds();
	if (!sounds.empty())
	{
		int i = sounds[RNG::generate(0, sounds.size() - 1)];
		if (i >= 0)
		{
			_parent->getMod()->getSoundByDepth(_parent->getDepth(), i)->play(-1, _parent->getMap()->getSoundAngle(_unit->getPosition()));
		}
	}
}

}
