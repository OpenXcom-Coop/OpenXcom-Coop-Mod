#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
 * Copyright 2023-2026 XComCoopTeam (https://www.moddb.com/mods/openxcom-coop-mod)
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

namespace OpenXcom
{

class BattleUnit;
class BattleItem;
class SavedBattleGame;

/**
 * R2-P4 (rewrite spike, SPIKE-RUNBOOK.md RB-D7): CLIENT-side id -> pointer
 * maps for BattleUnit/BattleItem. The host never needs this: it owns every
 * object and resolves ptr -> id trivially via getId(). A client only ever
 * gets ids over the wire (bt_ev/bt_action_end payloads name actors/targets
 * by id, per SS2.3/SS2.4) and needs the reverse lookup to touch the actual
 * object - hence one global map pair, CLIENT-side only, never built on the
 * host.
 *
 * Storage lives in connectionTCP.cpp (RB-D6 pattern, same as
 * BattleAuthority/CoopPump/CoopEmit) - this header only declares the API.
 * Dependency-light on purpose (BattleUnit/BattleItem/SavedBattleGame are
 * forward-declared only): full definitions are needed only in the .cpp
 * bodies, which already include all three.
 *
 * Lifecycle:
 *  - rebuildFrom(save): full scan of save->getUnits()/save->getItems(),
 *    called after a battle blob load. R4-P1 lands the actual client battle
 *    blob load path (SPIKE-RUNBOOK.md SS2.7's battle_ready sequence: verify
 *    sha -> loadCoopSaveFromMemory-equivalent -> CoopIdMaps::rebuildFrom ->
 *    authority -> full sweep -> battle_ready); this packet ships only the
 *    function itself, with the "R4-P1 calls rebuildFrom here" call-site note
 *    left in its doc comment in connectionTCP.cpp. No marker is planted at
 *    an existing call site: the only loadCoopSaveFromMemory calls in this
 *    tree today are SavedGame's (the geoscape/world blob) - a different
 *    object with a different loader - so there is nothing real to mark yet;
 *    R4-P1 is building a new SavedBattleGame-blob load path from scratch.
 *  - registerItem/registerUnit, forget/forgetUnit: incremental maintenance,
 *    called by the R3 S2 appliers as they create/destroy objects mid-battle.
 *    R2-P4 provides the bodies now so R3 has nothing left to wire here.
 *  - reset(): clears both maps. R2-P8 wires the real call at the battle
 *    teardown chokepoint (clearNetworkSessionQueues() family,
 *    connectionTCP.cpp - see the "R2-P8 teardown calls reset" marker); this
 *    packet provides the function only.
 */
namespace CoopIdMaps
{

/// Full rescan of @a save's units + items, replacing both maps wholesale
/// (RB-D7: "REBUILT by full scan after every blob load"). Safe to call with
/// save == nullptr (both maps are simply cleared, matching reset()).
void rebuildFrom(SavedBattleGame* save);

/// Reverse lookups. Return nullptr if @a id is not currently mapped (never
/// mints/creates - the S2 appliers own object creation, RB-D25).
BattleUnit* unit(int id);
BattleItem* item(int id);

/// Incremental maintenance, called by the R3 S2 appliers around object
/// creation. Keyed by @a *->getId(). Overwrites any existing entry for the
/// same id (last write wins - the appliers are expected to forget() before
/// an id is reused, never the other way around).
void registerItem(BattleItem* item);
void registerUnit(BattleUnit* unit);

/// Incremental maintenance, called by the R3 S2 appliers around object
/// destruction. No-op if the id is not currently mapped.
void forget(int itemId);
void forgetUnit(int unitId);

/// Teardown chokepoint (R2-P8 wires the call site): clears both maps back
/// to empty.
void reset();

} // namespace CoopIdMaps

} // namespace OpenXcom
