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

#include <string>
#include <vector>

#include <json/json.h>

namespace OpenXcom
{

class SavedBattleGame;
class BattlescapeState;

/**
 * W1-P13b (WAVE1-RUNBOOK.md SPEC 10 / REV E.48 SC / REV E.50): the END-TURN
 * readiness tally, SS2.W3's FROZEN wire pair:
 *
 *   bt_end_turn_ready {state, battleId, seat, turn:int, ready:bool}  client->host
 *   bt_end_turn_tally {state, battleId, turn:int, side, ready:[seat...],
 *                       count:int, needed:int}                       host->all
 *
 * Both are top-level messages (no `payload`) and both bypass the seq-ordered
 * apply queue - they are `bt_`-prefixed (battle lane) but neither `bt_ev` nor
 * `bt_action_end`, so BattleWire.h's isSeqOrdered() already routes them to
 * the direct lane dispatcher with NO edit to that file (SS2.1's own routing
 * predicate).
 *
 * PARALLEL MODE ONLY (SPEC 10 (b)). `activeSeat` (the traditional baton,
 * W1-P13c) is NOT implemented here and no predicate below may hard-code
 * "all seats" in a way P13c cannot parameterize later.
 *
 * ALL LOGIC LIVES IN src/CoopMod (body: connectionTCP.cpp, next to
 * CoopSideTransition's own W1-P13a scaffolding - the two packets share the
 * same boundary quiescence point). The vanilla touch is exactly
 * BattlescapeState::btnEndTurnClick's existing coop guard (widened, not
 * duplicated) plus the two small accessors declared on BattlescapeState
 * itself (getCoopEndTurnArmed() / the paired arming setter) - see that
 * class's own doc comments.
 *
 * `turn` here is the HOST-MINTED SIDE-PHASE COUNTER (IR2-4 / WV-D46) -
 * incremented once per APPLIED side_transition, NEVER read from or written
 * to SavedBattleGame::_turn. `needed` is the count of LIVE seats (WR-20 /
 * REV E.48 C.4): a CONNECTED seat with at least one live commandable unit on
 * the ACTIVE side. A side with zero human seats is INERT: no tally is ever
 * emitted for it and no press can arm anything, though the counter still
 * advances through it.
 */
namespace CoopEndTurn
{

/// Battle-scoped reset, called from resetBattleAuthority() (connectionTCP.cpp)
/// so a new battle never inherits the previous one's side-phase counter,
/// ready map, or tallies-seen count.
void reset();

/// HOST-ONLY (self-guarded: isCoopBattle() && hostSim). Called from
/// coopEmitSideTransition() (CoopSideTransition.h) immediately after its own
/// side_begin ev has gone out - the same per-boundary quiescence point
/// W1-P13a already uses. Implements SS2.W3's boundary discipline: (1)
/// increments the side-phase counter, (2) clears every stored ready bit,
/// (3) recomputes `needed` for the NEW side, (4) re-emits the tally - unless
/// the new side has zero human seats, in which case the tally stays INERT
/// (no wire message; the counter still advanced).
void onSideTransition(SavedBattleGame* save);

/// CLIENT-ONLY (self-guarded). Called from CoopApply::applyEvPayload()'s
/// "side_transition" branch, once per applied restate - this machine's own
/// mirror of the side-phase counter, used ONLY to stamp this machine's own
/// bt_end_turn_ready presses (SS2.W3: "the client stamps turn from the last
/// APPLIED side_transition, never from a wire value it has not applied
/// yet"). Never driven by an incoming bt_end_turn_tally.
void onClientAppliedSideTransition();

/// A seat departing mid-side changes the live-seat set (WR-20): recomputes
/// `needed`, discards the departed seat's own stored ready, and re-emits the
/// tally. HOST-ONLY (self-guarded); called from the host's own client-drop
/// teardown path. A no-op with no live battle.
void onSeatSetChanged(SavedBattleGame* save);

/// BattlescapeState::btnEndTurnClick's (widened) coop guard, for BOTH the
/// host's own press and a client's. Toggles THIS machine's own readiness bit
/// (the inverse of @a bs's current getCoopEndTurnArmed()) and either applies
/// it directly + broadcasts (host) or paints it optimistically + ships
/// bt_end_turn_ready for the host to confirm/undo (client). Self-guarded
/// (isCoopBattle()); the caller only reaches this inside an active coop
/// battle, so SP never does.
void toggleReady(BattlescapeState* bs);

/// Host-inbound: a client's bt_end_turn_ready. HOST-ONLY (self-guarded). A
/// press whose `turn` does not match the current side-phase counter is
/// DROPPED and answered with a re-emitted tally to the whole battle (WR-4) -
/// never a silent drop.
void onReadyReceived(const Json::Value& msg);

/// Inbound bt_end_turn_tally: adopts it into THIS machine's presentation
/// (the inverted button + the persistent text) and event_state snapshot,
/// bumping the tallies-seen counter. The HOST never receives its own
/// broadcast over the wire (2-machine transport) - its own emitTally() path
/// applies the same snapshot directly instead of round-tripping.
void onTallyReceived(const Json::Value& msg);

/// W1-P13b tool code (REV E.48 SS.A.6's closed lever list, the
/// battle_teleport_unit discipline): the test-only
/// `battle_end_turn_ready {turn, ready}` lever. Ships the SS2.W3
/// bt_end_turn_ready message with THIS machine's own seat and the GIVEN
/// `turn`, touching no local state - so the harness can CONSTRUCT a stale
/// press deterministically (REV E.48 C.2) instead of racing for one. Never
/// forwarded, nothing emitted beyond the one message, never called from
/// product code.
void testSendReady(int turn, bool ready);

// ----- event_state introspection (REV E.48 C.2 / F171; test-only, never
// read by game logic) -----

/// The raw side-phase counter, current value - the "3 vs 1" and
/// "advances exactly once per cycle" assertions both need this distinct
/// from tallyTurn() below, which stays frozen through an INERT phase.
int phaseCounter();

/// The last APPLIED-or-EMITTED (non-inert) tally's own fields.
int tallyTurn();
std::string tallySide();
int tallyCount();
int tallyNeeded();
std::vector<int> tallyReadySeats();

/// How many genuine (non-inert) tallies this machine has emitted-or-applied
/// this battle - the "+1" REV E.48 C.2 asserts on a real tally application.
/// Does NOT move on an inert boundary.
int talliesSeen();

} // namespace CoopEndTurn

} // namespace OpenXcom
