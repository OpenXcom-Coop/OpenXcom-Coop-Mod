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

#include <cstdint>

#include <json/json.h>

namespace OpenXcom
{

class BattleUnit;

/**
 * R2-P5 (rewrite spike, SPIKE-RUNBOOK.md RB-D9/RB-D10/RB-D11/RB-D12/RB-D13/
 * RB-D19, SS2.3/SS2.5/SS2.6): the HOST-side admission arbiter. Every bt_intent
 * lands here (via the R2-P1 lane dispatcher's "R2-P5/P6/P9 will handle
 * directly here" marker in connectionTCP.cpp's onTCPMessage) and is either
 * admitted (executed immediately + bt_ack) or denied (bt_deny{reason}, one of
 * SS2.2's machine enum strings). Deny-only (SS2.5, OWNER-2 resolved): NO
 * host-side queue exists in the spike - a denied client holds/resubmits
 * (R2-P7, not this packet). Kept behind this one seam (onIntent) so a future
 * 1-slot host queue could be added post-v1 without touching the wire.
 *
 * Bodies live in connectionTCP.cpp, next to BattleAuthority/CoopIdMaps/
 * CoopPump/CoopEmit - R2-P1..P4's established home for this scaffolding.
 */
namespace CoopArbiter
{

/// Host: the lane dispatcher calls this with one parsed bt_intent envelope
/// (SS2.3: {state, iseq, seat, actorId, kind, ...concrete-plan fields}).
/// Resolves the actor, checks not_your_unit / turn_over / busy (SS2.5), then
/// dispatches to validateTurn()/validateKneel() for the kind-specific
/// cost/well-formedness checks. On a clean pass: mints an actionId, ACKs
/// (CoopWire::makeAck), pushes an action context, and executes immediately
/// (RB-D10's donor-reproduction for turn, RB-D13's direct kneel() wrap for
/// kneel). On any check failing: denies (CoopWire::makeDeny) and returns - no
/// host-side queue (SS2.5). No-op (logs) outside an active coop battle or
/// with no live SavedBattleGame.
void onIntent(const Json::Value& intent);

/// Host: RB-D11/RB-D12 quiescence hook - called (via the coopOnChainQuiesced()
/// free-function forwarder below) from BattlescapeGame::popState() at the
/// exact point the popped BState chain leaves _states empty. If a coop
/// action context is on top of the stack, emits the pending bt_action_end
/// for the just-finished chain-ful action (turn) and pops the context,
/// clearing this battle's "chain busy" state so the next intent can be
/// admitted. No-op if the action-context stack is empty (a popState with no
/// coop action in flight - e.g. a foreign/AI chain) or outside an active coop
/// battle.
void onChainQuiesced();

/// Pushes {actionId, origin} onto CoopMod's own action-context stack
/// (RB-D12 - no BState code stores coop state). @a origin is one of SS2.2's
/// origin enum strings; RB-D19's "host" is reserved for the host-seat's own
/// direct input (R3's emit hooks). This packet's own arbiter-admitted-intent
/// push sites use "intent" - SS2.2's frozen 7-value enum has no entry for
/// "a validated non-host client intent" yet (see this packet's final report
/// for the gap and why "intent" was minted as a placeholder pending an
/// SS2.2 update).
void pushActionContext(std::uint32_t actionId, const char* origin);

/// The actionId on top of the action-context stack, or 0 if the stack is
/// empty (SS2.2: 0 is never a minted actionId, so 0 doubles as "none").
std::uint32_t currentActionId();

/// SS2.5 turn validator: cost + well-formedness only (see this packet's
/// final report for why not_your_unit/turn_over/busy - which need the
/// intent's seat and the live BattlescapeGame - are checked by onIntent()
/// itself instead, ahead of this call, rather than in here; the given
/// signature carries neither). Returns nullptr if @a toDir/@a turret/
/// @a tuBasis admit cleanly against @a unit's current state; otherwise one
/// of SS2.2's deny reason enum strings (never an ad-hoc string).
const char* validateTurn(const BattleUnit* unit, int toDir, bool turret, int tuBasis);

/// SS2.5 kneel validator, same contract/caveat as validateTurn().
const char* validateKneel(const BattleUnit* unit, bool kneel, int tuBasis);

} // namespace CoopArbiter

/// RB-D11: the free-function forwarder the vanilla BattlescapeGame::popState
/// thin hook calls (kept outside namespace CoopArbiter so the vanilla call
/// site needs no extra namespace qualification beyond OpenXcom's own).
/// Forwards to CoopArbiter::onChainQuiesced(). Guarded internally (the .cpp
/// body no-ops outside an active coop battle) so the vanilla call site stays
/// a single unconditional call.
void coopOnChainQuiesced();

} // namespace OpenXcom
