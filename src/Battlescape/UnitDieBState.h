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
#include "../Mod/RuleItem.h"

namespace Json { class Value; }

namespace OpenXcom
{

class BattlescapeGame;
class BattleUnit;
struct CoopDeathGhost;

/* Refactoring tip : UnitDieBState */
/**
 * State for dying units.
 */
class UnitDieBState : public BattleState
{
private:
	BattleUnit *_unit;
	const RuleDamageType *_damageType;
	bool _noSound;
	int _extraFrame;
	bool _overKill;
	bool _coop_death;
	// coop (chain-atomicity Strand A): latched at CONSTRUCTION - this death was
	// pushed inside a BOUNDARY-phase checkForCasualties pass (side-close / side-start
	// fuse+terrain+environmental+bleed-out), so its unit_death/after_unit_death must
	// stay seq-0 and ride the ordered boundary marker's hash rather than opening a
	// loose mid-side chain. Mirrors ExplosionBState::_coopBoundaryExpl. init() runs a
	// think() later - after the synchronous boundary bracket has closed - so the phase
	// MUST be captured now, not read live at send time.
	bool _coopBoundaryDeath = false;
	// coop (parallel battlescape Phase 2c - death ghost): non-null in GHOST MODE only.
	// A ghost is a display-only UnitDieBState the parallel replay client pushes AFTER
	// coopApplyCasualty already applied the death atomically (state is final: dead,
	// tile-unlinked, corpse minted). Ghost mode replays the vanilla collapse animation
	// on the victim's BattleUnit display-override fields (never its real state) and
	// SKIPS every world mutation + every host-only send/notify. nullptr in every
	// existing path - so no existing behaviour changes.
	const CoopDeathGhost* _ghost = nullptr;
	/// coop (Phase 2c): the ghost-mode per-tick animation (display overrides only).
	void coopGhostThink();
  public:
	/// Creates a new UnitDieBState class
	UnitDieBState(BattlescapeGame* parent, BattleUnit* unit, const RuleDamageType* damageType, bool noSound, bool coop_death = false);
	/// coop (Phase 2c - death ghost): the display-only ctor. Drives the collapse
	/// animation off @a ghost's captured pose while the real unit stays final.
	UnitDieBState(BattlescapeGame* parent, const CoopDeathGhost* ghost);
	/// Cleans up the UnitDieBState.
	~UnitDieBState();
	/// Initializes the state.
	void init() override;
	/// coop (PRD-P10): ships `after_unit_death` the moment the state POPS.
	void deinit() override;
	/// Handles a cancels request.
	void cancel() override;
	/// Runs state functionality every cycle.
	void think() override;
	/// coop: stamps killedBy/murdererId (the host's kill attribution) on a death packet.
	void coopWriteKillAttribution(Json::Value& root) const;
	/// coop (PRD-I3 SEAM-4): every living unit's absolute morale after this casualty.
	void coopWriteBystanderMorale(Json::Value& root) const;
	/// Converts a unit to a corpse.
	void convertUnitToCorpse();
	/// Plays the death sound.
	void playDeathSound();
};

}
