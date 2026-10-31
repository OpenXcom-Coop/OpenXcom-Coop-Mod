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
 * CLIENT-side id -> pointer
 * maps for BattleUnit/BattleItem. The host never needs this: it owns every
 * object and resolves ptr -> id trivially via getId(). A client only ever
 * gets ids over the wire (bt_ev/bt_action_end payloads name actors/targets
 * by id) and needs the reverse lookup to touch the actual
 * object - hence one global map pair, CLIENT-side only, never built on the
 * host.
 *
 * Storage lives in connectionTCP.cpp (same pattern as
 * BattleAuthority/CoopPump/CoopEmit) - this header only declares the API.
 * Dependency-light on purpose (BattleUnit/BattleItem/SavedBattleGame are
 * forward-declared only): full definitions are needed only in the .cpp
 * bodies, which already include all three.
 *
 * Lifecycle:
 *  - rebuildFrom(save): full scan of save->getUnits()/save->getItems(),
 *    called after a battle blob load (the client's battle_ready sequence:
 *    verify sha -> loadCoopSaveFromMemory-equivalent -> CoopIdMaps::rebuildFrom
 *    -> authority -> full sweep -> battle_ready).
 *  - registerItem/registerUnit, forget/forgetUnit: incremental maintenance,
 *    called by the appliers as they create/destroy objects mid-battle.
 *  - reset(): clears both maps. Called at the battle teardown chokepoint
 *    (clearNetworkSessionQueues() family, connectionTCP.cpp).
 */
namespace CoopIdMaps
{

/// Full rescan of @a save's units + items, replacing both maps wholesale
/// (rebuilt by full scan after every blob load). Safe to call with
/// save == nullptr (both maps are simply cleared, matching reset()).
void rebuildFrom(SavedBattleGame* save);

/// Reverse lookups. Return nullptr if @a id is not currently mapped (never
/// mints/creates - the appliers own object creation).
BattleUnit* unit(int id);
BattleItem* item(int id);

/// Incremental maintenance, called by the appliers around object
/// creation. Keyed by @a *->getId(). Overwrites any existing entry for the
/// same id (last write wins - the appliers are expected to forget() before
/// an id is reused, never the other way around).
void registerItem(BattleItem* item);
void registerUnit(BattleUnit* unit);

/// Incremental maintenance, called by the appliers around object
/// destruction. No-op if the id is not currently mapped.
void forget(int itemId);
void forgetUnit(int unitId);

/// Teardown chokepoint: clears both maps back
/// to empty.
void reset();

} // namespace CoopIdMaps

} // namespace OpenXcom
