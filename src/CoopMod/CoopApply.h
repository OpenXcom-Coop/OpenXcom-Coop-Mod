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

#include <json/json.h>

namespace OpenXcom
{

class BattleUnit;
class SavedBattleGame;

/**
  * coop: the client-side state applier for the turn/kneel atoms. Called from
 * CoopDisplayQueue::onApplied() (BattlePump.h) - the seam
 * CoopPump::drainApplyQueue() invokes, in strict seq order, for
 * every bt_ev/bt_action_end AFTER the gap check and BEFORE
 * CoopHashCheck::verify()'s post-apply hash compare.
 *
  * Rules: pump-only (never called off the main/pump thread - true by
  * construction, since drainApplyQueue() itself is main-thread-only),
  * payload-only writes (only the fields a payload/final actually carries are
  * touched), no pushState/popState/BState op (this never runs vanilla
  * simulation, it copies already-decided host state), and a targeted per-unit
  * FOV refresh done by the CALLER (CoopDisplayQueue::onApplied(),
  * connectionTCP.cpp) immediately after each apply - not in here, since this
  * namespace never touches SavedBattleGame beyond resolving the unit
  * (CoopIdMaps::unit()).
 *
  * Fields written: direction, turret direction, time units, the kneeled bit,
  * and energy. Position is deliberately EXCLUDED (turn/kneel never move a
  * unit; syncing position is the walk atom's job, not this one's). Resolution
  * is EXCLUSIVELY via CoopIdMaps - this never mints a BattleUnit/BattleItem;
  * the .cpp body sits inside a MINT-WHITELIST-BEGIN/END region even though
  * nothing in it actually mints.
 *
 * Body lives in connectionTCP.cpp, next to BattleAuthority/CoopArbiter/
  * CoopIdMaps/CoopPump/CoopEmit.
 */
namespace CoopApply
{

/// Applies one in-order bt_ev's payload to the unit it names
/// (payload["unit"], resolved via CoopIdMaps::unit()). Handles
/// kind "turn" (body facing from toDir unless turretOnly, turret facing
/// ALWAYS and ONLY from turretTo - see the body's own
/// setBodyDirectionKeepTurret() comment - plus tuAfter) and kind "kneel"
/// (kneeled, tuAfter); any other kind (including inject_ev's
/// test payloads, e.g. "spot") is a state-no-op, logged
/// "UNSUPPORTED <kind>" - legal because those test payloads carry no state. A
/// "turn" payload's optional "door" field is likewise never applied
/// (logged "UNSUPPORTED door-in-turn"): terrain apply is the door atom's
/// job. No-op (logs) if @a save is null, the payload carries no "unit", or
/// the named unit does not resolve on this machine.
void applyEvPayload(SavedBattleGame* save, const Json::Value& ev);

/// Applies one bt_action_end's "final" object ({pos, dir, tu, energy,
/// kneeled}) to @a unit - EXCEPT "pos" (see this namespace's own
/// doc comment: turn/kneel never move a unit, applying position is out of
/// this applier's scope). No-op if @a unit is null (the caller's actionId
/// correlation - connectionTCP.cpp's CoopDisplayQueue::onApplied() - is
/// what can produce a null here, e.g. a foreign actionId this machine never
/// saw the opening bt_ev for).
void applyActionEndFinal(BattleUnit* unit, const Json::Value& final);

} // namespace CoopApply

} // namespace OpenXcom
