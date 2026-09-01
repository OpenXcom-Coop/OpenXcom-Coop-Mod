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

// ----- CLIENT section (RB-D32) -----

/// CLIENT: the shared intent-builder - "one function, two callers" (RB-D32).
/// Builds a bt_intent envelope (CoopWire::makeIntent, SS2.3) from EXPLICIT
/// plan fields, mints this machine's client-local iseq (this namespace's own
/// counter - separate from the HOST-side actionId mint above; reset at the
/// same battle-teardown chokepoint), computes @a kind's tuBasis the same way
/// the client preview would (turn: Sigma per-tick getTurnCost/1-per-tick-if-
/// turret over the shortest-arc tick count, mirroring validateTurn()'s own
/// recompute; kneel: getKneelChangeCost()) UNLESS @a tuBasisOverride is >= 0,
/// in which case it REPLACES the recomputed basis (the G5 stale-basis lever,
/// RB-D32's own text). Ships via CoopEmit::sendBattle - never touches the
/// host-side action-context stack or executes anything locally (RB-D32: "do
/// NOT build turn EXECUTION here; just build+send the intent envelope" - the
/// admitted intent's real execution happens on the HOST machine, inside
/// onIntent() above, exactly like any other bt_intent sender).
///
/// Caller #1 (R2-P11): TestServer's battle_intent command. Caller #2 (R3-P1):
/// the RB-D10 UI intercepts (BattlescapeGame::secondaryAction /
/// BattlescapeState::btnKneelClick) - PLACE new callers here, never a second
/// copy of the envelope-building logic.
///
/// @a kind is "turn" or "kneel" (SS2.3's spike intent kinds, RB-D9). @a toDir/
/// @a turret apply to "turn"; @a kneel applies to "kneel". Returns the minted
/// iseq, or 0 on failure (SS2.2: 0 is never a valid iseq a caller should treat
/// as sent) - outside an active coop battle, with no live SavedBattleGame,
/// if @a actorId does not resolve on THIS machine, or for an unknown @a kind.
std::uint32_t sendClientIntent(const char* kind, int actorId, int toDir = -1,
	bool turret = false, bool kneel = false, int tuBasisOverride = -1);

} // namespace CoopArbiter

/// RB-D11: the free-function forwarder the vanilla BattlescapeGame::popState
/// thin hook calls (kept outside namespace CoopArbiter so the vanilla call
/// site needs no extra namespace qualification beyond OpenXcom's own).
/// Forwards to CoopArbiter::onChainQuiesced(). Guarded internally (the .cpp
/// body no-ops outside an active coop battle) so the vanilla call site stays
/// a single unconditional call.
void coopOnChainQuiesced();

} // namespace OpenXcom
