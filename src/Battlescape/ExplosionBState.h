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
#include "BattleState.h"
#include "Position.h"

namespace OpenXcom
{

class BattlescapeGame;
class BattleUnit;
class BattleItem;
class Tile;
struct RuleDamageType;

/**
 * Explosion state not only handles explosions, but also bullet impacts!
 * Refactoring tip : ImpactBState.
 */
class ExplosionBState : public BattleState
{
private:
	int _explosionCounter;
	int _terrainMeleeTilePart;
	BattleActionAttack _attack;
	Position _center, _before;
	const RuleDamageType *_damageType;
	Tile *_tile;
	BattleUnit *_targetPsiOrHit;
	int _power;
	int _radius;
	int _range;
	bool _areaOfEffect, _lowerWeapon, _hit, _psi;
	// coop (PRD-I3 SEAM-3 a): set on an explosion that ORIGINATES in the endTurn
	// boundary phase (a fuse detonation or a boundary terrain explosion), and
	// inherited by any terrain-chain consequence it spawns. A boundary explosion is
	// deliberately NOT given its own admitted chain - its destroys are applied before
	// the endturn/sidestart boundary marker's hash on both machines, so the ordered
	// boundary compare already covers them; opening a mid-phase chain there would
	// interleave an action_end with the boundary markers.
	bool _coopBoundaryExpl = false;
	// coop (chain-atomicity D.3b): the auto-shot pacing "parked, awaiting the host's
	// flip" flag, now PER-INSTANCE (it was a file-scope global shared by every
	// ExplosionBState). Only a shot-origin explosion (_explosionCounter == 0) ever
	// parks on it; a chained-terrain consequence (_explosionCounter > 0) can neither
	// set nor clear another instance's, so it can never consume this shot's flip nor
	// starve its wait. The host flip channel (_hasHitUnit, on the CoopMod) stays
	// shared - the per-instance flag is what routes a release to the parked shot.
	bool _coopTaskCompleted = false;
	// coop (explosion ordered-replay E1): latched ONCE near the top of init() so it
	// persists into think()/member explode(). True only on a parallel client that has
	// not had the replay lever forced off (parallelTurnActive() && !getHost() &&
	// !g_explosionReplayDisable) - on that machine this ExplosionBState becomes
	// DISPLAY-ONLY: the authoritative explode() ray-trace (init, single call) and
	// checkForCasualties (member explode()) are gated on it. The blast ANIMATION is
	// unaffected - only those two sim calls. Host / classic co-op / PvP / single-player
	// always compute this false, so they are byte-identical to pre-E1.
	bool _coopReplayDisplay = false;

	/// Calculates the effects of the explosion.
	void explode();
	/// Set new value to reference if new value is not equal -1.
	void optValue(int &oldValue, int newValue) const;
public:
	/// coop (PRD-I3 SEAM-3 a): flag/read this explosion as a boundary-phase origin.
	void coopSetBoundaryExpl(bool b) { _coopBoundaryExpl = b; }
	bool coopBoundaryExpl() const { return _coopBoundaryExpl; }
	/// Creates a new ExplosionBState class.
	ExplosionBState(BattlescapeGame *parent, LastPositions center, BattleActionAttack attack, Tile *tile = 0, bool lowerWeapon = false, int range = 0, int explosionCounter = 0, int terrainMeleeTilePart = 0);
	/// Cleans up the ExplosionBState.
	~ExplosionBState();
	/// Initializes the state.
	void init() override;
	/// Handles a cancel request.
	void cancel() override;
	/// Runs state functionality every cycle.
	void think() override;

};

}
