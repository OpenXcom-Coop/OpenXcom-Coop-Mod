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

#include "ExplosionBState.h"
#include "BattlescapeState.h"
#include "Explosion.h"
#include "TileEngine.h"
#include "Map.h"
#include "Camera.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleItem.h"
#include "../Mod/Armor.h"
#include "../Engine/RNG.h"
#include <atomic>

namespace OpenXcom
{

// coop (chain-atomicity D.3b): the auto-shot pacing "parked, awaiting the host's flip"
// flag is now a PER-INSTANCE member (ExplosionBState::_coopTaskCompleted), not a file-scope
// global. A file-scope global was shared by every live ExplosionBState, so a chained-terrain
// explosion (checkForTerrainExplosions, _explosionCounter > 0) could park on it or consume
// the shot's host flip - the D.3b wedge. The member confines the pacing flag to the one shot
// that parked it.

// coop (chain-atomicity D.3b fixture instrumentation): the chained-terrain pacing race,
// counted at the bug site. A chained-terrain consequence (checkForTerrainExplosions,
// _explosionCounter > 0, BA_NONE) must NEVER touch the shot-pacing signal. These monotonic
// counters make the race observable through parallel_state (TestServer extern-reads them):
//   g_coopTerrainPacingParks    = a chained-terrain that PARKED on the shot-pacing flag
//   g_coopTerrainPacingConsumes = a chained-terrain whose think() release CONSUMED the flip
//   g_coopTerrainPacingDiverted = a chained-terrain that reached the pacing decision while
//                                 the shot-pacing condition was live and was DIVERTED off
//                                 the park path by the _explosionCounter == 0 gate (the fix)
// Parks/consumes are the BUG (non-zero only before the fix); diverted proves the fix engaged
// on the same opportunity. All three are parallel-client only and inert (0) otherwise.
std::uint32_t g_coopTerrainPacingParks = 0;
std::uint32_t g_coopTerrainPacingConsumes = 0;
std::uint32_t g_coopTerrainPacingDiverted = 0;

// coop (explosion ordered-replay E1): the replay-lever + display-only counters are
// file-scope in connectionTCP.cpp (alongside the E0 objective-leak counters); extern-
// declared here so this file can read/increment them without a wide recompile, matching
// the pattern the D.3b counters above use in reverse (defined here, extern-read by
// TestServer.cpp). g_explosionReplayDisable is the E0-introduced TEST-ONLY lever
// (E0 only stored + surfaced it; E1 is what actually wires it to force the legacy
// racing-sim path). g_explosionsDisplayOnly / g_explodeCallsSuppressed are new this
// phase: the former counts ExplosionBState instances that took the display-only path
// (latched once per state, right after _coopReplayDisplay), the latter counts how many
// times the single explode() call at init() was suppressed by it.
extern std::atomic<bool> g_explosionReplayDisable;
extern std::atomic<uint32_t> g_explosionsDisplayOnly;
extern std::atomic<uint32_t> g_explodeCallsSuppressed;

// coop (explosion ordered-replay E2): the chain_detonation send/apply counters, file-scope
// in connectionTCP.cpp alongside the E1 counters above; extern-declared here so this file's
// parallel-host send site can increment the sent side. g_chainDetonationsSent counts every
// chain_detonation the parallel host ships (its successive checkForTerrainExplosions scan
// hits); g_chainDetonationsApplied (incremented in connectionTCP.cpp's handler) counts every
// one the parallel client replays. The two must match at side close - a mismatch means the
// ordered chain stream dropped or duplicated a secondary.
extern std::atomic<uint32_t> g_chainDetonationsSent;
extern std::atomic<uint32_t> g_chainDetonationsApplied;

/**
 * Sets up an ExplosionBState.
 * @param parent Pointer to the BattleScape.
 * @param center Center position in voxelspace.
 * @param item Item involved in the explosion (eg grenade).
 * @param unit Unit involved in the explosion (eg unit throwing the grenade).
 * @param tile Tile the explosion is on.
 * @param lowerWeapon Whether the unit causing this explosion should now lower their weapon.
 * @param range Distance between weapon and target.
 * @param explosionCounter Counter for chain terrain explosions.
 * @param terrainMeleeTilePart Tile part for terrain melee.
 */
ExplosionBState::ExplosionBState(BattlescapeGame *parent, LastPositions center, BattleActionAttack attack, Tile *tile, bool lowerWeapon, int range, int explosionCounter, int terrainMeleeTilePart) : BattleState(parent),
	_explosionCounter(explosionCounter), _terrainMeleeTilePart(terrainMeleeTilePart), _attack(attack), _center(center.last), _before(center.before), _damageType(), _tile(tile), _targetPsiOrHit(nullptr),
	_power(0), _radius(6), _range(range), _areaOfEffect(false), _lowerWeapon(lowerWeapon), _hit(false), _psi(false)
{

}

/**
 * Deletes the ExplosionBState.
 */
ExplosionBState::~ExplosionBState()
{

}

/**
 * Set new value to reference if new value is not equal -1.
 * @param oldValue old value to change.
 * @param newValue new value to set, but only if is not equal -1.
 */
void ExplosionBState::optValue(int& oldValue, int newValue) const
{
	if (newValue != -1)
	{
		oldValue = newValue;
	}
}

/**
 * Initializes the explosion.
 * The animation and sound starts here.
 * If the animation is finished, the actual effect takes place.
 */
void ExplosionBState::init()
{
	// coop (explosion ordered-replay E1): latch ONCE, near the top, so the value
	// persists into think()/member explode() for the whole life of this state. True
	// only on a parallel client whose replay lever has not been forced off - see the
	// member declaration in ExplosionBState.h. g_explosionReplayDisable is the E0-
	// introduced lever E1 now actually wires (RED: forces the client back onto the
	// old racing explode()/checkForCasualties path, same build).
	_coopReplayDisplay = _parent->getCoopMod()->parallelTurnActive()
		&& !_parent->getCoopMod()->getHost()
		&& !OpenXcom::g_explosionReplayDisable.load(std::memory_order_relaxed);
	if (_coopReplayDisplay)
	{
		++OpenXcom::g_explosionsDisplayOnly;
	}

	BattleType type = BT_NONE;
	BattleActionType action = _attack.type;
	const RuleItem* itemRule = 0;
	bool miss = false;
	if (_attack.damage_item)
	{
		itemRule = _attack.damage_item->getRules();
		type = itemRule->getBattleType();

		_power = 0;
		_hit = action == BA_HIT;
		_psi = type == BT_PSIAMP && action != BA_USE && !_hit;
		if (_hit && type != BT_MELEE)
		{
			_power += itemRule->getMeleeBonus(_attack);

			_radius = 0;
			_damageType = itemRule->getMeleeType();
		}
		else
		{
			if (_attack.weapon_item && _attack.weapon_item->getRules()->getIgnoreAmmoPower())
			{
				_power += _attack.weapon_item->getRules()->getPowerBonus(_attack);
				_power -= _attack.weapon_item->getRules()->getPowerRangeReduction(_range);
			}
			else
			{
				_power += itemRule->getPowerBonus(_attack);
				_power -= itemRule->getPowerRangeReduction(_range);
			}

			_radius = itemRule->getExplosionRadius(_attack);
			_damageType = itemRule->getDamageType();
		}

		if (type == BT_PSIAMP || _hit)
		{
			Position targetPos = _center.toTile();
			_targetPsiOrHit = _parent->getSave()->getTile(targetPos)->getOverlappingUnit(_parent->getSave());
		}

		//testing if we hit target
		if (action == BA_SELF_DESTRUCT)
		{
			// coop (PRD-P3 GAP-4b): the host rolled this in BattleUnit::damage, before
			// the selfDestruct packet went out, and parked the answer here.
			auto* coopSD = _parent->getCoopMod();
			bool triggered;
			// coop (wire-order Increment 3 / A2): prefer the parallel client's display-side
			// copy (populated at the selfDestruct receiver-park lever-on) so next_turn's
			// state-half clear cannot starve this replay. Empty lever-off / on the host, so
			// it falls through to the canonical queue, then the RNG roll, byte-identically.
			if (coopSD && coopSD->getCoopStatic() && !coopSD->_selfDestructResultsDisplay.empty())
			{
				triggered = coopSD->_selfDestructResultsDisplay.front() != 0;
				coopSD->_selfDestructResultsDisplay.erase(coopSD->_selfDestructResultsDisplay.begin());
			}
			else if (coopSD && coopSD->getCoopStatic() && !coopSD->_selfDestructResults.empty())
			{
				triggered = coopSD->_selfDestructResults.front() != 0;
				coopSD->_selfDestructResults.erase(coopSD->_selfDestructResults.begin());
			}
			else
			{
				triggered = RNG::percent(itemRule->getSpecialChance());
			}
			if (!triggered)
			{
				_power = 0;
			}
		}
		else if (type == BT_PSIAMP && !_hit)
		{
			if (action != BA_USE)
			{
				_power = 0;
			}
			if (!_parent->getTileEngine()->psiAttack(_attack, _targetPsiOrHit))
			{
				_power = 0;
				miss = true;
			}
			else
			{
				_parent->psiAttackMessage(_attack, _targetPsiOrHit);
			}
		}
		else if (type == BT_MELEE || _hit)
		{
			if (!_parent->getTileEngine()->meleeAttack(_attack, _targetPsiOrHit, _terrainMeleeTilePart))
			{
				_power = 0;
				miss = true;
			}
		}
		else if (type == BT_FIREARM)
		{
			if (_power <= 0)
			{
				miss = true;
			}
		}

		_areaOfEffect = type != BT_MELEE && _radius != 0 &&
						(type != BT_PSIAMP || action == BA_USE) &&
						!_hit && !miss;
	}
	else if (_tile)
	{
		ItemDamageType DT;
		switch (_tile->getExplosiveType())
		{
		case 0:
			DT = DT_HE;
			break;
		case 5:
			DT = DT_IN;
			break;
		case 6:
			DT = DT_STUN;
			break;
		default:
			DT = DT_SMOKE;
			break;
		}
		_power = _tile->getExplosive();
		// coop (chain-atomicity item-2): the tile's explosive-charge CONSUMPTION is
		// host-authoritative terrain bookkeeping, not display. On the parallel replay
		// client this zero used to run LOCALLY off the display loop, racing the
		// destroy_tile ARM carrier - so the charge (a saveBlob/terrain hash term) could
		// diverge between machines and drive a chained explosion one machine never ran.
		// The client now applies the host's stamped set_explosive_tile(0) instead (shipped
		// below), keeping the charge purely packet-driven. Host / classic co-op / PvP /
		// single-player zero exactly as before; the _power read above still feeds the
		// animation radius on every machine.
		const bool coopExplReplayClient =
			_parent->getCoopMod()->parallelTurnActive() && !_parent->getCoopMod()->getHost();
		if (!coopExplReplayClient)
		{
			_tile->setExplosive(0, 0, true);
		}
		_damageType = _parent->getMod()->getDamageType(DT);
		_radius = _power /10;
		_areaOfEffect = true;
	}
	else
	{
		_power = 120;
		_damageType = _parent->getMod()->getDamageType(DT_HE);
		_areaOfEffect = true;
	}


	bool range = !(_hit || (_attack.weapon_item && _attack.weapon_item->getRules()->getBattleType() == BT_PSIAMP));

	// coop (PRD-I3 SEAM-3 a): a mid-side explosion running with no open admitted chain
	// (a shot/grenade whose action already drained, or a spontaneous detonation) owns its
	// own seq so the destroy_tile/hazard outcome it is about to emit rides the I1 gate
	// instead of shipping seq-0 always-consume. Boundary-phase explosions are excluded -
	// their destroys ride the ordered endturn/sidestart boundary compare already.
	if (!_coopBoundaryExpl)
	{
		connectionTCP::coopStampLooseOutcomeChain("expl");
	}

	// coop (chain-atomicity item-2): ship the host's explosive-charge CONSUMPTION as a
	// stamped set_explosive_tile carrier so the parallel replay client mirrors the zero
	// at the bookkeeping clock - ordered behind this tile's destroy_tile ARM and drained
	// ahead of the chain's action_end (D.1 barrier), exactly like destroy_tile.
	// coopStampChainSeq tags it with the loose chain opened just above (mid-side) or
	// leaves it seq-0 for a boundary explosion (applied before the boundary hash, as
	// boundary destroy_tile already is). Host-only + parallel-PvE-only: classic co-op,
	// PvP and single-player never ship it and the replay client's suppression above is
	// likewise parallel-gated, so those paths stay byte-identical. Only a real
	// consumption (_power > 0) ships; the tile is already zeroed on the host above.
	if (_tile && _power > 0
		&& _parent->getCoopMod()->parallelTurnActive() && _parent->getCoopMod()->getHost())
	{
		Json::Value root;
		root["state"] = "set_explosive_tile";
		connectionTCP::coopStampChainSeq(root);
		const Position tpos = _tile->getPosition();
		root["tile_pos_x"] = tpos.x;
		root["tile_pos_y"] = tpos.y;
		root["tile_pos_z"] = tpos.z;
		root["explosive"] = _tile->getExplosive();
		root["explosive_type"] = _tile->getExplosiveType();
		connectionTCP::sendTCPPacketStaticData2(root.toStyledString());
	}

	if (_areaOfEffect)
	{
		if (_power > 0)
		{
			// coop (explosion ordered-replay E1): the authoritative ray-trace. On a
			// display-only parallel client this is SUPPRESSED - terrain/charge/fire/
			// smoke/item/FOV outcomes arrive as carriers (destroy_tile, set_explosive_tile,
			// set_fire_tile, set_smoke_tile, explode_items, calc_explode_fov), unit damage
			// as hit_unit - and the explode-path gravity/objective/module writes simply
			// stop happening at the source instead of racing the carriers. The ANIMATION
			// below is UNCONDITIONAL - only this one call is gated. Host / classic co-op /
			// PvP / single-player: _coopReplayDisplay is always false, so this call is
			// unchanged (byte-identical to pre-E1).
			if (!_coopReplayDisplay)
			{
				_parent->getSave()->getTileEngine()->explode(_attack, _center, _power, _damageType, _radius, range);
			}
			else
			{
				++OpenXcom::g_explodeCallsSuppressed;
			}

			int powerForAnimation = _power;
			if (itemRule && itemRule->getPowerForAnimation() > 0)
			{
				powerForAnimation = itemRule->getPowerForAnimation();
			}

			int frame = Mod::EXPLOSION_OFFSET;
			int frameCount = -1;
			int sound = powerForAnimation <= 80 ? Mod::SMALL_EXPLOSION : Mod::LARGE_EXPLOSION;

			if (itemRule)
			{
				frame = itemRule->getHitAnimation();
				frameCount = itemRule->getHitAnimationFrames();
				optValue(sound, itemRule->getExplosionHitSound());
			}
			if (_parent->getDepth() > 0)
			{
				frame -= (frameCount > 0 ? frameCount : Explosion::EXPLODE_FRAMES);
			}
			int frameDelay = 0;
			int counter = std::max(1, (powerForAnimation / 5) / 5);
			_parent->getMap()->setBlastFlash(true);
			int lowerLimit = std::max(1, powerForAnimation / 5);
			for (int i = 0; i < lowerLimit; i++)
			{
				int X = RNG::generate(-powerForAnimation / 2, powerForAnimation / 2);
				int Y = RNG::generate(-powerForAnimation / 2, powerForAnimation / 2);
				Position p = _center;
				p.x += X; p.y += Y;
				Explosion *explosion = new Explosion(p, frame, frameDelay, true, false, frameCount);
				// add the explosion on the map
				_parent->getMap()->getExplosions()->push_back(explosion);
				if (i > 0 && i % counter == 0)
				{
					frameDelay++;
				}
			}
			int explosionSpeed = BattlescapeState::DEFAULT_ANIM_SPEED/2;
			if (itemRule)
			{
				explosionSpeed -= (10 * itemRule->getExplosionSpeed());
			}
			if (_explosionCounter > 6)
			{
				explosionSpeed = 1; // maximum animation speed for long chain terrain explosions
			}
			_parent->setStateInterval(std::max(1, explosionSpeed));
			// explosion sound
			_parent->playSound(sound);
			if (_parent->getMap()->getFollowProjectile() || _explosionCounter > 0)
			{
				_parent->getMap()->getCamera()->centerOnPosition(_center.toTile(), false);
			}
		}
		else
		{
			_parent->popState();
		}
	}
	else
	// create a bullet hit
	{
		_parent->getSave()->getTileEngine()->hit(_attack, _center, _power, _damageType, range, _terrainMeleeTilePart);

		_parent->setStateInterval(std::max(1, ((BattlescapeState::DEFAULT_ANIM_SPEED/2) - (10 * itemRule->getExplosionSpeed()))));
		int anim = -1;
		int animFrames = -1;
		int sound = -1;

		const RuleItem *weaponRule = _attack.weapon_item->getRules();
		const RuleItem *damageRule = _attack.weapon_item != _attack.damage_item ? itemRule : nullptr;

		if (_hit || _psi)
		{
			anim = weaponRule->getMeleeAnimation();
			animFrames = weaponRule->getMeleeAnimationFrames();
			if (_psi)
			{
				// psi attack sound is based weapon hit sound
				sound = weaponRule->getHitSound();

				optValue(anim, weaponRule->getPsiAnimation());
				optValue(animFrames, weaponRule->getPsiAnimationFrames());
				optValue(sound, weaponRule->getPsiSound());
			}
			else
			{
				sound = weaponRule->getMeleeSound();
				if (damageRule)
				{
					optValue(anim, damageRule->getMeleeAnimation());
					optValue(animFrames, damageRule->getMeleeAnimationFrames());
					optValue(sound, damageRule->getMeleeSound());
				}
			}
		}
		else
		{
			anim = itemRule->getHitAnimation();
			animFrames = itemRule->getHitAnimationFrames();
			sound = itemRule->getHitSound();
		}

		if (miss)
		{
			if (_hit || _psi)
			{
				optValue(anim, weaponRule->getMeleeMissAnimation());
				optValue(animFrames, weaponRule->getMeleeMissAnimationFrames());
				if (_psi)
				{
					// psi attack sound is based weapon hit sound
					optValue(sound, weaponRule->getHitMissSound());

					optValue(anim, weaponRule->getPsiMissAnimation());
					optValue(animFrames, weaponRule->getPsiMissAnimationFrames());
					optValue(sound, weaponRule->getPsiMissSound());
				}
				else
				{
					optValue(sound, weaponRule->getMeleeMissSound());
					if (damageRule)
					{
						optValue(anim, damageRule->getMeleeMissAnimation());
						optValue(animFrames, damageRule->getMeleeMissAnimationFrames());
						optValue(sound, damageRule->getMeleeMissSound());
					}
				}
			}
			else
			{
				optValue(anim, itemRule->getHitMissAnimation());
				optValue(animFrames, itemRule->getHitMissAnimationFrames());
				optValue(sound, itemRule->getHitMissSound());
			}
		}

		if (anim != -1)
		{
			Explosion *explosion = new Explosion(_center, anim, 0, false, (_hit || _psi), animFrames); // Don't burn the tile
			_parent->getMap()->getExplosions()->push_back(explosion);
		}
		if (_parent->getMap()->getFollowProjectile())
		{
			_parent->getMap()->getCamera()->setViewLevel(_center.z / 24);
		}

		if (_targetPsiOrHit && _parent->getSave()->getSide() == FACTION_HOSTILE && _targetPsiOrHit->getFaction() == FACTION_PLAYER)
		{
			_parent->getMap()->getCamera()->centerOnPosition(_center.toTile(), false);
		}
		// bullet hit sound
		_parent->playSound(sound, _center.toTile());
	}

	if (_attack.type == BA_SELF_DESTRUCT)
	{
		if (_attack.attacker)
		{
			_attack.attacker->setAlreadyExploded(false);
		}
	}
}

/**
 * Animates explosion sprites. If their animation is finished remove them from the list.
 * If the list is empty, this state is finished and the actual calculations take place.
 */
void ExplosionBState::think()
{

	// coop (Class-A soak wedge fix): this auto-shot pacing wait (below) is the ONE
	// display state that can hold the receive gate for the rest of the battle - via
	// the ProjectileFlyBState beneath it - when its flip packet never lands (a
	// host/client multi-shot count divergence, likeliest on hazard-heavy turns).
	// updateCoopTask watches _coopPacingWait and, once it has been held past the
	// stall floor, raises _coopForceDrainReplay so the wait can end instead of
	// starving the gate forever. Release AS IF the flip had landed: -2 also stops
	// projectileHitUnit re-arming this wait for the remaining shots (it only arms on
	// -1), so a wedged multi-shot drains in one pass rather than one escape per shot.
	if (_coopTaskCompleted && _parent->getCoopMod()->_coopForceDrainReplay)
	{
		_parent->getCoopMod()->_coopForceDrainReplay = false;
		_parent->getCoopMod()->_coopPacingWait = false;
		_parent->getCoopMod()->_hasHitUnit = -2;
		_coopTaskCompleted = false;
		_parent->popState();
		return;
	}

	//  coop
	if (_coopTaskCompleted && (_parent->getCoopMod()->_hasHitUnit == -1 || _parent->getCoopMod()->_hasHitUnit == -2))
	{
		// D.3b guard: with the per-instance flag a chained-terrain (_explosionCounter > 0)
		// never has its OWN _coopTaskCompleted set, so it can never reach this release and
		// consume the shot's flip. Post-fix this stays 0; a non-zero value means a chained-
		// terrain leaked onto the pacing path again.
		if (_explosionCounter > 0) ++g_coopTerrainPacingConsumes;
		_coopTaskCompleted = false;
		_parent->getCoopMod()->_coopPacingWait = false;
		_parent->popState();
		return;
	}

	if (!_parent->getMap()->getBlastFlash())
	{
		if (_parent->getMap()->getExplosions()->empty())
			explode();

		for (auto iter = _parent->getMap()->getExplosions()->begin(); iter != _parent->getMap()->getExplosions()->end();)
		{
			Explosion* explosion = (*iter);
			if (!explosion->animate())
			{
				delete explosion;
				iter = _parent->getMap()->getExplosions()->erase(iter);
				if (_parent->getMap()->getExplosions()->empty())
				{
					explode();
					return;
				}
			}
			else
			{
				++iter;
			}
		}
	}
}

/**
 * Explosions cannot be cancelled.
 */
void ExplosionBState::cancel()
{
}

/**
 * Calculates the effects of the explosion.
 */
void ExplosionBState::explode()
{
	bool terrainExplosion = false;
	SavedBattleGame *save = _parent->getSave();
	// last minute adjustment: determine if we actually
	if (_hit)
	{
		if (_attack.attacker && !_attack.attacker->isOut())
		{
			_attack.attacker->aim(false);
		}

		if (_power <= 0)
		{
			_parent->popState();
			return;
		}

		int sound = _attack.weapon_item->getRules()->getMeleeHitSound();
		if (_attack.weapon_item != _attack.damage_item)
		{
			// melee weapon with ammo
			optValue(sound, _attack.damage_item->getRules()->getMeleeHitSound());
		}
		_parent->playSound(sound, _center.toTile());
	}

	if (_tile)
	{
		terrainExplosion = true;
	}
	if (!_tile && !_attack.damage_item)
	{
		terrainExplosion = true;
	}

	// now check for new casualties
	// coop (chain-atomicity Strand A): a BOUNDARY explosion (side-close fuse/terrain, run
	// BEFORE coopArmSyncBoundary arms its marker) is excluded from the loose-chain stamp
	// above, so it dies with _openChainSeq == 0; without this bracket the UnitDieBState it
	// pushes would latch _coopBoundaryDeath == false and open a mid-side chain. Flag the
	// phase so those deaths stay seq-0 (covered by the ordered boundary marker). A mid-side
	// explosion (opened a loose chain above) passes false, so its deaths ride that chain.
	_parent->coopSetBoundaryCasualty(_coopBoundaryExpl);
	// coop (explosion ordered-replay E1): on a display-only parallel client, casualty
	// resolution is SUPPRESSED here - death/knockout arrive as unit_casualty (atomic-death
	// Phase 2) instead of being computed locally. The coopSetBoundaryCasualty bracket
	// above/below keeps running unconditionally (cheap chain bookkeeping, harmless even
	// when the call it brackets is skipped). Host / classic co-op / PvP / single-player
	// unchanged.
	if (!_coopReplayDisplay)
	{
		_parent->checkForCasualties(_attack.damage_item ? _damageType : nullptr, _attack, false, terrainExplosion);
	}
	_parent->coopSetBoundaryCasualty(false);
	// revive units if damage could give hp or reduce stun
	_parent->getSave()->reviveUnconsciousUnits(true);
	// if any unit get infected turn it to zombie
	_parent->convertInfected();

	// if this explosion was caused by a unit shooting, now it's the time to put the gun down
	if (_attack.attacker && !_attack.attacker->isOut() && _lowerWeapon)
	{
		_attack.attacker->aim(false);
	}

	if (_attack.damage_item && (_attack.damage_item->getRules()->getBattleType() == BT_GRENADE || _attack.damage_item->getRules()->getBattleType() == BT_PROXIMITYGRENADE))
	{
		_parent->getSave()->removeItem(_attack.damage_item);
	}

	// coop (chain-atomicity D.3b): only a SHOT-origin explosion (_explosionCounter == 0)
	// may park on the auto-shot pacing path. The park flag is per-instance
	// (_coopTaskCompleted), and the extra _explosionCounter == 0 gate keeps a
	// chained-terrain consequence (spawned below by checkForTerrainExplosions, with
	// _explosionCounter > 0 and BA_NONE) off this path entirely: it never parks on the
	// shared host flip and never clears the shot's _coopPacingWait. Before the fix a
	// terrain-chain ExplosionBState read the same file-scope flag and could park on or
	// consume the shot's flip (or, once gated to the else, reset the RX pump's stall floor
	// mid-chain), starving the shot's pacing wait - the ~10 s client wedge bounded only by
	// the force-drain watchdog.
	const bool coopPacingCandidate =
		_parent->getCoopMod()->getCoopStatic() == true
		&& _parent->getCoopMod()->getHost() == false
		&& _parent->getCoopMod()->_hasHitUnit == 1;
	if (_explosionCounter == 0 && coopPacingCandidate)
	{
		_coopTaskCompleted = true;
		// coop (Class-A soak wedge fix): flag the pacing wait live so the RX pump's
		// stall floor (updateCoopTask) can force-drain it if the flip never comes.
		_parent->getCoopMod()->_coopPacingWait = true;
	}
	else if (_explosionCounter == 0)
	{
		// a shot-origin explosion that is NOT pacing (host side, single shot, or the
		// flip already landed): clear the wait and finish, exactly as before.
		_parent->getCoopMod()->_coopPacingWait = false;
		_parent->popState();
	}
	else
	{
		// a chained-terrain consequence: it must never touch the shot-pacing signal, so
		// leave _coopPacingWait owned by whatever shot parked it and just finish. D.3b: it
		// is DIVERTED off the park path here - count it while a shot's pacing wait is live
		// (the same race window that PARKED it before the fix), so the regression test can
		// prove the fix engaged on a real race rather than on a vacuous run. _coopPacingWait
		// (not _hasHitUnit==1) is the window: it stays set for the whole wait, whereas
		// _hasHitUnit flips to -2 the moment the now-uncontested flip lands.
		if (_parent->getCoopMod()->getCoopStatic() == true
			&& _parent->getCoopMod()->getHost() == false
			&& _parent->getCoopMod()->_coopPacingWait)
		{
			++g_coopTerrainPacingDiverted;
		}
		_parent->popState();
	}

	// coop (explosion ordered-replay E2): the whole chained-terrain scan+spawn block is
	// host/classic/PvP/SP only now. On the parallel client (_coopReplayDisplay) this whole-
	// map checkForTerrainExplosions scan raced independently on both machines (each machine's
	// scan order could differ), so a parallel client no longer scans or spawns chained
	// secondaries locally - it replays them in the host's scan order from the chain_detonation
	// stream instead (handler in connectionTCP.cpp). This also removes the item-2 "stranded"
	// tile problem entirely: that hack existed only to converge a parallel CLIENT's own
	// (independently-ordered) scan hitting its own explosion's tile; a client that never scans
	// can never strand on it.
	if (!_coopReplayDisplay)
	{
		// check for terrain explosions
		Tile *t = save->getTileEngine()->checkForTerrainExplosions();
		if (t)
		{
			Position p = t->getPosition().toVoxel();
			p += Position(8,8,0);
			// coop (explosion ordered-replay E2): the parallel host ships one chain_detonation
			// per secondary it spawns so the client detonates them in THIS host's scan order
			// (its successive scans are the order). explosive/type ride the packet - by the time
			// the client displays this the tile's charge may already be zeroed by a
			// set_explosive_tile carrier. coopStampChainSeq tags it with the triggering chain
			// (mid-side) or leaves it seq-0 for a boundary explosion, exactly like the item-2
			// set_explosive_tile carrier above. Parallel-host-only; classic/PvP/SP ship nothing.
			if (_parent->getCoopMod()->parallelTurnActive() && _parent->getCoopMod()->getHost())
			{
				Json::Value root;
				root["state"] = "chain_detonation";
				connectionTCP::coopStampChainSeq(root);
				const Position tp = t->getPosition();
				root["tile_pos_x"] = tp.x; root["tile_pos_y"] = tp.y; root["tile_pos_z"] = tp.z;
				root["explosive"] = t->getExplosive();
				root["explosive_type"] = t->getExplosiveType();
				connectionTCP::sendTCPPacketStaticData2(root.toStyledString());
				++OpenXcom::g_chainDetonationsSent;
				OpenXcom::chainDetonationListRecord(tp.x, tp.y, tp.z);
			}
			// coop (PRD-I3 SEAM-3 a): a terrain-chain consequence inherits this explosion's
			// origin - a boundary chain stays boundary (excluded from the loose stamp); a
			// mid-side chain stays inside the seq this explosion opened, so it never re-stamps.
			ExplosionBState *chained = new ExplosionBState(_parent, p, BattleActionAttack{ BA_NONE, _attack.attacker, }, t, false, 0, _explosionCounter + 1);
			chained->coopSetBoundaryExpl(_coopBoundaryExpl);
			_parent->statePushFront(chained);
		}
	}

	// Spawn a unit if the item does that
	if (_attack.damage_item)
	{
		_parent->spawnNewUnit(_attack, _before.toTile());
	}

	// Spawn a item if the weapon does that
	if (_attack.damage_item)
	{
		_parent->spawnNewItem(_attack, _before.toTile());
	}
}

}
