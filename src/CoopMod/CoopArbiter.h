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

/// Host: RB-D19 origin stamping for a coop HOST's own local turn (SS2.5:
/// "host-local player input never enters the intent path" - it always runs
/// vanilla directly, never onIntent()). Called from the THIN
/// BattlescapeGame::secondaryAction hook site's own-input branch (R3-P1),
/// BEFORE it pushes UnitTurnBState, mirroring onIntent()'s turn-branch
/// bookkeeping (mint actionId, push {actionId,"host"} action context, record
/// @a actor as this chain's pending actor plus its pre-turn direction/
/// turret-direction) so UnitTurnBState::think()'s completion hook
/// (coopOnUnitTurnFinished below) and onChainQuiesced()'s bt_action_end emit
/// both fire correctly for the host's OWN turns too, exactly as they already
/// do for an admitted remote intent. No-op outside an active coop battle (the
/// vanilla call site stays a single unconditional call, like
/// coopOnChainQuiesced()).
void beginHostLocalTurn(BattleUnit* actor, bool turret);

/// Host: RB-D19 origin stamping for a coop HOST's own local kneel - the
/// chain-less (RB-D13) counterpart to beginHostLocalTurn() above. Called
/// from the THIN BattlescapeState::btnKneelClick hook site's own-input
/// branch (R3-P2), BEFORE it calls BattlescapeGame::kneel(bu), mirroring
/// onIntent()'s "kneel" branch bookkeeping (mint actionId, push
/// {actionId,"host"} action context, record @a actor as this kneel's
/// pending actor) so the THIN emit hook inside BattlescapeGame::kneel()
/// itself (coopOnKneelFinished below) fires correctly for the host's OWN
/// kneel too, exactly as it already does for an admitted remote intent. No
/// BState/quiescence involved (RB-D13 - kneel resolves synchronously inside
/// the single kneel() call this begins). No-op outside an active coop
/// battle (the vanilla call site stays a single unconditional call, like
/// beginHostLocalTurn()).
void beginHostLocalKneel(BattleUnit* actor);

/// Pushes {actionId, origin} onto CoopMod's own action-context stack
/// (RB-D12 - no BState code stores coop state). @a origin is one of SS2.2's
/// origin enum strings; RB-D19's "host" is reserved for the host-seat's own
/// direct input (R3's emit hooks). The arbiter's own admitted-intent push
/// sites use "intent" - a FIRST-CLASS SS2.2 origin value since WAVE1-RUNBOOK
/// SS2.W7 / WV-D15 froze the enum as "ai | endturn | reaction | panic |
/// script | prox | host | intent". R2-P5 minted "intent" as a placeholder
/// ahead of that freeze (connectionTCP.cpp:2095, :2148); W1-P1 closed the
/// gap, so the value is no longer provisional.
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

/// CLIENT (R3-P1, REVIEW4 IR-2): host bt_ack{iseq,actionId} receipt - if
/// @a ack's iseq matches this client's own in-flight intent (set by a prior
/// sendClientIntent() call that actually shipped), records the actionId so a
/// later bt_action_end (which carries no unit/iseq of its own, only
/// actionId, SS2.3) can be recognized as "mine" by onActionEndApplied()
/// below. No-op if the iseq does not match (a stale/foreign ack, or nothing
/// in flight) or outside an active coop battle.
void onAck(const Json::Value& ack);

/// CLIENT (R3-P1, IR-2): host bt_deny{iseq,reason} receipt - always updates
/// lastDeny() below (event_state's own field, R2-P11) and shows the
/// CoopBattleUi::showDeny() banner; additionally clears this client's own
/// in-flight lock if @a deny's iseq matches it. No-op (does not even update
/// lastDeny) outside an active coop battle.
///
/// R2-P7 CHANGE (packet text, "Common core"): reason=="busy" on THIS
/// client's own in-flight intent no longer drops it (R3-P1's explicit
/// "pre-R2-P7 deny(busy) behavior = banner + DROP" is superseded here).
/// The plan is moved into the PENDING slot, CoopBattleUi::showPending()
/// raises the SS2.6 busy banner, and it is auto-resubmitted at the next
/// event_state-visible quiescence (see onQuiescenceObserved() below). Every
/// OTHER deny reason keeps R3-P1's banner+drop behavior exactly.
void onDeny(const Json::Value& deny);

/// CLIENT (R3-P1, IR-2): called by CoopDisplayQueue::onApplied()
/// (BattlePump.h/connectionTCP.cpp) once a bt_action_end has been applied -
/// clears this client's own in-flight lock if @a actionId matches it (the
/// acted-upon unit becomes send-able again via sendClientIntent()). No-op
/// for a foreign actionId (this client did not initiate it, e.g. it belongs
/// to another seat or to the host's own local input) or if nothing is in
/// flight.
void onActionEndApplied(std::uint32_t actionId);

/// event_state's lastDeny field (R2-P11's own RW-TODO(R3-P1) marker in
/// TestServer.cpp, now filled): the {iseq,reason} object from the most
/// recent onDeny() this CLIENT machine received this battle, or
/// Json::Value() (null) if none yet.
Json::Value lastDeny();

// ----- R2-P7: CLIENT auto-retry + info-cancel -----

/// CLIENT (R2-P7): called by CoopDisplayQueue::onApplied() for every applied
/// bt_action_end, AFTER onActionEndApplied() has resolved this client's own
/// in-flight lock. This is the packet text's "event_state-visible
/// quiescence" signal: the host emits bt_action_end only from
/// onChainQuiesced() (RB-D11), so applying one is exactly the client-visible
/// proof that the blocker's chain has unwound. If a PENDING intent is held,
/// it is resubmitted here through sendClientIntent() - which RECOMPUTES the
/// preview + tuBasis against CURRENT client state (packet text), never
/// replays a stale basis. A resubmit that is busy-denied again simply goes
/// pending again (self-sustaining until it is admitted, cancelled by policy,
/// or cancelled by the user). No-op outside an active coop battle or with
/// nothing pending.
void onQuiescenceObserved();

/// CLIENT (R2-P7): the info-cancel policy evaluation point - called by
/// CoopDisplayQueue::onApplied() for every applied bt_ev, AFTER the payload
/// has been applied (so the visibility-gain check reads post-apply state).
/// Evaluates the four Options:: toggles (coopCancelOnEnemySpotted /
/// OwnUnitHit / VisibilityGain / AnyPartnerAction), read LIVE per the packet
/// text, against @a ev and cancels the pending intent via
/// CoopBattleUi::showCancel() naming the trigger (SS2.6 - never a generic
/// message). @a visibleBefore is the pre-apply local visible-hostile count
/// from visibleHostileCount() below (the toggle-3 basis). No-op with nothing
/// pending, outside an active coop battle, or with every toggle off.
void onEvAppliedCancelCheck(const Json::Value& ev, int visibleBefore);

/// CLIENT (R2-P7): the toggle-3 basis - how many distinct HOSTILE units are
/// currently visible to units this machine's seat commands. Purely local FOV
/// state (D4 machine-local, presentation-legal per the packet's own
/// "local-FOV visibility-gain check on apply" wording); never hashed, never
/// on the wire. Returns 0 with no live battle.
int visibleHostileCount();

/// CLIENT (R2-P7): the user-facing CANCEL CONTROL ("right-click/ESC clears",
/// packet text). Returns true iff a pending intent existed and was dropped -
/// the two thin vanilla hook sites use that to CONSUME the input
/// (BattlescapeGame::secondaryAction's client branch, so a right-click
/// clears the held order instead of issuing a second one; and
/// BattlescapeState::handle's SDLK_ESCAPE arm). Clears the banner via
/// CoopBattleUi::clearPending(). False (and completely inert) outside an
/// active coop battle or with nothing pending, so both call sites stay a
/// single guarded call.
bool cancelPendingIntent();

/// Test/introspection (TestServer battle_state): the held plan as
/// {kind, actorId, iseq} - iseq being the iseq of the intent whose busy deny
/// created it - or Json::Value() (null) when nothing is pending.
Json::Value pendingIntent();

// ----- R2-P7: hold_chain test lever (HOST) -----

// TEST-ONLY STOPGAP (owner 2026-09-02): delete/replace with a real shot-based busy once the shot atom lands (r3 fan-out) - a slow auto-shot is the natural long chain.
/// HOST (RB-D26/RB-D32 family, owner-approved 2026-09-02): arm a one-shot
/// latch that keeps the NEXT quiesced BState chain artificially OPEN for
/// @a ms milliseconds - onChainQuiesced() defers its bt_action_end emit and
/// its action-context pop, so onIntent()'s `currentActionId() != 0` arm keeps
/// answering deny("busy") for the whole window. Without it a live busy deny
/// cannot be landed at all: R3-P2 measured a full 4-tick UnitTurnBState chain
/// resolving in well under one TestServer round trip (spike-log R3-P2 GAP).
void requestHoldChain(std::uint32_t ms);

// TEST-ONLY STOPGAP (owner 2026-09-02): delete/replace with a real shot-based busy once the shot atom lands (r3 fan-out) - a slow auto-shot is the natural long chain.
/// HOST: the release half of requestHoldChain() - ONE unconditional guarded
/// call at the RB-D5 pump point (next to CoopReveal::flushQuiescent()). Once
/// the hold window expires this re-enters onChainQuiesced(), which then runs
/// its normal emit+pop. Completely inert with no hold armed.
void releaseHeldChainIfExpired();

// ----- W1-P7: order feedback (WAVE1-RUNBOOK.md ruling D7 = WV-D13) -----

/// MACHINE-RELATIVE: the co-op SEAT that owns the action currently occupying
/// the HOST's single execution slot, or -1 when nothing is running / this
/// machine cannot attribute it. The seat-attributed
/// STR_COOP_WAIT_FOR_PLAYER_ACTION driver (WV-D13 item 4) reads it.
///
/// HOST arm: the SS2.5 busy predicate - `BattlescapeGame::isBusy()` OR an open
/// action context (`currentActionId() != 0`, which is also what a held
/// hold_chain window keeps true). The owner is LATCHED once per busy window,
/// donor semantics (`cbff7951d:BattlescapeState.cpp:5310-5327`): consequence
/// states (death/fall/explosion) are pushed to the FRONT of the queue mid-chain,
/// so re-deriving the owner every tick would mis-attribute a kill to the victim's
/// side. Resolved from `BattlescapeGame::getPrimaryBusyActor()` (the donor call
/// site, restored this packet) and, when the chain has already unwound but its
/// action context is still open, from the arbiter's own pending-chain actor.
///
/// CLIENT arm: a thin client pushes NO BStates (BattlePump.h: "appliers set flags
/// only"), so `isBusy()` is always false there and the donor predicate cannot be
/// used as-is. The client's equivalent knowledge is its own intent bookkeeping:
/// its OWN admitted-and-unfinished action (a bt_ack recorded, its bt_action_end
/// not yet applied) means the blocker is ITSELF; otherwise, while a busy-denied
/// intent is held, the blocker is the only OTHER seat there can be. The
/// other-seat branch is deliberately gated on `seatCount() == 2` - the same
/// 2-player bridge the donor's own name fallback carries, and for the same
/// reason: there is no wire field that names a busy owner, so with 3+ seats this
/// returns -1 and the presenter falls back to the generic SS2.6 busy row rather
/// than guessing. NO new wire field is added for this (SS2.2/SS2.3 unchanged).
int busyOwnerSeat();

/// CLIENT: is a busy-denied intent currently HELD in the pending slot? Read by
/// the wait-banner driver (a client is only 'waiting' while it holds one).
bool hasPendingIntent();

/// CLIENT (WV-D24 = ruling D-11): the intent round-trip TIMEOUT tick. ONE
/// unconditional guarded call from the RB-D5 pump point (CoopBattleUi::tick()).
/// Fires `Options::coopIntentTimeoutSeconds` after the in-flight intent was sent
/// (default 10 s; <= 0 disables): raises STR_COOP_ACTION_TIMEOUT and RELEASES the
/// IR-2 one-slot input lock, which is the bug it exists to fix - before this, a
/// lost intent locked its unit for the rest of the battle.
///
/// The timed-out iseq is remembered for the rest of the battle and a late
/// `bt_ack` / `bt_deny` carrying it is PERMANENTLY IGNORED (WV-D24, exactly): it
/// updates no lastDeny, raises no banner and re-locks nothing - it only bumps
/// lateAnswersIgnored() below so a test can prove the message ARRIVED and was
/// ignored rather than never came. A late `bt_action_end` still APPLIES
/// untouched: it is host truth and carries state, and nothing here is on the
/// apply path at all.
void tickIntentTimeout();

/// Test/introspection (TestServer event_state / battle_state): this CLIENT's
/// in-flight intent as {iseq, kind, actorId, actionId, ageMs}, or null when the
/// slot is empty. `actionId` is 0 until the host's bt_ack lands. The slot being
/// null after a timeout is the observable proof the IR-2 lock was released.
Json::Value inFlightIntent();

/// Test/introspection: how many intents have TIMED OUT on this machine this
/// battle, and the iseq of the most recent one (0 = none yet).
std::uint32_t intentTimeouts();
std::uint32_t lastTimedOutIseq();

/// Test/introspection: how many late bt_ack / bt_deny messages were ignored
/// because their iseq had already timed out. Makes WV-D24's "a late ack/deny
/// changes nothing" a DELIVERED-then-ignored assertion instead of an absence.
std::uint32_t lateAnswersIgnored();

// TEST-ONLY (W1-P7, RB-D26/RB-D32 discipline; same family and the same removal
// note as hold_chain above): delete once real-network latency/loss can be
// injected another way.
/// HOST: hold the next @a count incoming bt_intent messages for @a ms
/// milliseconds before dispatching them normally. This is the only way to make
/// WV-D24's timeout deterministic: it produces a real UNANSWERED intent (the
/// client times out), and then a real LATE answer on the wire (the host's ack or
/// deny, arriving after the client gave up) so the ignore rule is testable too.
/// @a ms 0 disarms.
void requestDeferIntents(std::uint32_t ms, int count);

// TEST-ONLY (W1-P7): the release half of requestDeferIntents() - ONE
// unconditional guarded call at the RB-D5 pump point, next to
// releaseHeldChainIfExpired(). Inert with nothing deferred.
void releaseDeferredIntentsIfExpired();

} // namespace CoopArbiter

/// RB-D11: the free-function forwarder the vanilla BattlescapeGame::popState
/// thin hook calls (kept outside namespace CoopArbiter so the vanilla call
/// site needs no extra namespace qualification beyond OpenXcom's own).
/// Forwards to CoopArbiter::onChainQuiesced(). Guarded internally (the .cpp
/// body no-ops outside an active coop battle) so the vanilla call site stays
/// a single unconditional call.
void coopOnChainQuiesced();

/// R3-P1 (SPIKE-RUNBOOK.md UnitTurnBState.cpp:104/:116/:142 @911ca487f): the
/// THIN completion/abort hook UnitTurnBState::think() calls, once, at
/// whichever branch actually pops its own state - never per 45-degree tick
/// (the intermediate think() calls that keep turning take neither exit
/// branch). Builds and sends bt_ev{kind:"turn"} (RB-D14: always carrying
/// h:{unitsStats}) from @a unit's CURRENT (post-turn) direction/turret-
/// direction/TU plus the "before" values CoopArbiter captured when this
/// chain began - either onIntent()'s turn branch (an admitted remote intent)
/// or beginHostLocalTurn() above (the host's own local click). No-op outside
/// an active coop battle, or if @a unit is not the actor CoopArbiter is
/// currently tracking a turn chain for (a foreign/AI/SP turn is never coop's
/// to report - kept outside namespace CoopArbiter for the same
/// call-site-simplicity reason as coopOnChainQuiesced()). @a aborted is
/// accepted for a diagnostic log line only: SPIKE-RUNBOOK.md RB-D15/REVIEW4
/// IR-4's fixture guards are constructed so a coop-admitted turn's abort
/// branches never fire in the spike's own repro - if one ever does anyway,
/// this still reports the actor's true post-abort state rather than
/// silently dropping the ev.
void coopOnUnitTurnFinished(BattleUnit* unit, bool aborted);

/// R3-P2 (SPIKE-RUNBOOK.md RB-D13 - "the arbiter wraps BattlescapeGame::
/// kneel(bu) directly: admit -> push context -> call -> emit bt_ev kneel +
/// bt_action_end -> pop context"): the THIN hook BattlescapeGame::kneel()
/// calls at BOTH of its own return points (the successful branch, right
/// before its own `return true`, and the shared `return false` exit) -
/// generalizes R2-P5's own inline admitted-intent-only kneel emit (which
/// this packet removes from CoopArbiter::onIntent()'s "kneel" branch) into
/// ONE shared completion point so it fires identically for BOTH origins the
/// packet text names: an admitted remote intent (onIntent()'s "kneel"
/// branch, which pushes {actionId,"intent"} + records @a unit as the
/// pending chain actor BEFORE calling kneel()) and the host's own local
/// click (beginHostLocalKneel() above, called from the RB-D10
/// BattlescapeState::btnKneelClick intercept). No-op outside an active coop
/// battle, or if @a unit is not the actor CoopArbiter is currently tracking
/// a kneel for (a foreign/AI/SP kneel is never coop's to report - kept
/// outside namespace CoopArbiter for the same call-site-simplicity reason
/// as coopOnChainQuiesced()/coopOnUnitTurnFinished()).
///
/// @a succeeded is kneel()'s own return value. validateKneel()'s own doc
/// comment (connectionTCP.cpp) names a deliberate gap: it does not
/// replicate vanilla kneel()'s TU-RESERVATION half of its precondition
/// (`(!isKneeled && getKneelReserved()) || checkReservedTU(...)`), so an
/// admitted intent can rarely still fail here even though this packet
/// otherwise treats validateKneel() as authoritative. When @a succeeded is
/// false this still emits a `halted:true` bt_action_end (no ev - nothing
/// changed) and still pops the action context, so the initiating client's
/// in-flight lock resolves instead of leaving the whole battle permanently
/// "busy" (the pushed context must be popped exactly once regardless of
/// which branch kneel() took).
void coopOnKneelFinished(BattleUnit* unit, bool succeeded);

} // namespace OpenXcom
